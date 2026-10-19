"""Replay the exact public provenance projection; never import native code.

Only the fixed20 JSON files/57 historical locator leaves and the manifest's20
child byte/hash entries may change. Original source is a separate frozen epoch.
The bridge records hashes, relative paths and pointers, never original locators.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

SCHEMA = 'rsb.public-source-projection/1'
MANIFEST = 'robosafebench/assets/data/realism_v3/manifest.json'
BEFORE_MANIFEST_SHA256 = '4c8457342a8c898d343245396db951114c57985930eea5efbb31a987f0d132f5'
BEFORE_MANIFEST_BYTES = 128735
ALLOWLIST = json.loads(r'''[
  {
    "before_bytes": 11429,
    "before_sha256": "4f0c6f99e6e75aebe7f2cb5d86000155d5838fbed77a50a9af6f5ef0f0fe4169",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/hand/pack.json",
    "pointers": [
      {
        "before_value_sha256": "61f78758c089eac3aa02c2ee4d59757a4e9ec46a92bd03558c1a28f87b317719",
        "pointer": "/cpu_v3/authored_skin_texture_resolution/validation/hl_L/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hl_L.glb"
      },
      {
        "before_value_sha256": "c749767d19f301eea33b4b20100fbac276eac191f40714a716f7059b9cb4bd7f",
        "pointer": "/cpu_v3/authored_skin_texture_resolution/validation/hl_R/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hl_R.glb"
      },
      {
        "before_value_sha256": "1eb5f1d2240bae0593d7a750e2b0da4f5e93d5d4c5b8f8b699f7c5297fb52b4a",
        "pointer": "/cpu_v3/authored_skin_texture_resolution/validation/hm_L/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hm_L.glb"
      },
      {
        "before_value_sha256": "6f43b3d463d09e3ecd48f0f9a83d6b5b2c8702c468cf624d642cd93a7a36ada5",
        "pointer": "/cpu_v3/authored_skin_texture_resolution/validation/hm_R/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hm_R.glb"
      },
      {
        "before_value_sha256": "7b7ae70872aaf7e01834b64ac10950328a743ed0521ffcb3030632b938436680",
        "pointer": "/cpu_v3/authored_skin_texture_resolution/validation/hd_L/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hd_L.glb"
      },
      {
        "before_value_sha256": "9aceb40aba0d5ba785096da047467cf3b8d77c788ea6ac2ddd8b9bb80c613765",
        "pointer": "/cpu_v3/authored_skin_texture_resolution/validation/hd_R/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hd_R.glb"
      }
    ],
    "realism_relative_path": "packs/hand/pack.json"
  },
  {
    "before_bytes": 14464,
    "before_sha256": "afae8fe4eea87e3d4e041804d3239040d14a59ad1bd17951481a3b35b07b33f7",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a1_down_prone_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "d11b9ca899b177e5ce2bd8fd68a5de23b1df26b81d71a6e6533bc52c009fe316",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/prone_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a1_down_prone_support_fit.json"
  },
  {
    "before_bytes": 15824,
    "before_sha256": "f286d062b481692f6445e8695f2f95fbeb702d13093bbc258e324b1e68cb64e6",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a1_down_side_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "f7109d7fb9a3880beb1382bbc377155ef4f30e92a94e789985da4bd9a340e116",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/side_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a1_down_side_support_fit.json"
  },
  {
    "before_bytes": 13338,
    "before_sha256": "3124b9fcd69eaf22f9810cc63515b9ea6099a1ce1bd759dbcaf3ea4cb00c31a7",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a2_down_prone_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "d11b9ca899b177e5ce2bd8fd68a5de23b1df26b81d71a6e6533bc52c009fe316",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/prone_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a2_down_prone_support_fit.json"
  },
  {
    "before_bytes": 15646,
    "before_sha256": "a840356f774d92bc4251ca8e9158c6b1e4b5384b44aeff99a656d1cc971e0fc5",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a2_down_side_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "f7109d7fb9a3880beb1382bbc377155ef4f30e92a94e789985da4bd9a340e116",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/side_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a2_down_side_support_fit.json"
  },
  {
    "before_bytes": 11342,
    "before_sha256": "368418320d01fd1e83f2ad5897fc8e0104c18d956219b3dcbd3ecf85946096ce",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a3_down_prone_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "d11b9ca899b177e5ce2bd8fd68a5de23b1df26b81d71a6e6533bc52c009fe316",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/prone_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a3_down_prone_support_fit.json"
  },
  {
    "before_bytes": 16575,
    "before_sha256": "b58d354a3a288413b0e5fe395a368ff135dbd940eb95b568be2e3f6982e5ad4c",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a3_down_side_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "f7109d7fb9a3880beb1382bbc377155ef4f30e92a94e789985da4bd9a340e116",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/side_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a3_down_side_support_fit.json"
  },
  {
    "before_bytes": 10919,
    "before_sha256": "6ac913372e69df7813d2de2ce9eefee560a49cbc69a6ab076949ff20fa3a6926",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a4_down_prone_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "d11b9ca899b177e5ce2bd8fd68a5de23b1df26b81d71a6e6533bc52c009fe316",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/prone_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a4_down_prone_support_fit.json"
  },
  {
    "before_bytes": 14191,
    "before_sha256": "159c8ae3073241f4f93ec70d72aae7cdf54b9abacd3b8e7a6f5c0a0312032879",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a4_down_side_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "f7109d7fb9a3880beb1382bbc377155ef4f30e92a94e789985da4bd9a340e116",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/side_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a4_down_side_support_fit.json"
  },
  {
    "before_bytes": 27272,
    "before_sha256": "62a97e96b485b31d00037b67c350b8a9c356fddbd714c9b8c0fbd1cd84dcac08",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a5_down_prone_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "d11b9ca899b177e5ce2bd8fd68a5de23b1df26b81d71a6e6533bc52c009fe316",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/prone_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a5_down_prone_support_fit.json"
  },
  {
    "before_bytes": 16584,
    "before_sha256": "885ebf591b7526e3d16b350283c892a2fd8d917825d3e7bc8259fe25d491da9c",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a5_down_side_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "f7109d7fb9a3880beb1382bbc377155ef4f30e92a94e789985da4bd9a340e116",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/side_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a5_down_side_support_fit.json"
  },
  {
    "before_bytes": 9520,
    "before_sha256": "eb8889392596938818ff0d30d8ebab21f1d593821258b371b03e3ab0a28aa871",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a6_down_prone_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "d11b9ca899b177e5ce2bd8fd68a5de23b1df26b81d71a6e6533bc52c009fe316",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/prone_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a6_down_prone_support_fit.json"
  },
  {
    "before_bytes": 15132,
    "before_sha256": "ba2422de964cab076782b6cb06ed4364ffc3aeaf4bd53610f8326aa8f3a18651",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/a6_down_side_support_fit.json",
    "pointers": [
      {
        "before_value_sha256": "f7109d7fb9a3880beb1382bbc377155ef4f30e92a94e789985da4bd9a340e116",
        "pointer": "/target_json",
        "replacement": "historical-source://calibration/pose_fix/side_target.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/a6_down_side_support_fit.json"
  },
  {
    "before_bytes": 10415,
    "before_sha256": "c4aa5b59822c5fea7caabfd2ca55a66dd6e22663a60f71414e717b4901997373",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/target_prone.json",
    "pointers": [
      {
        "before_value_sha256": "b1e3280c4ec28a912ad65697d08980bc9087aa9070ac445d3b3a35f7d34a8651",
        "pointer": "/source_spec",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/specs/a6_down_prone.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/target_prone.json"
  },
  {
    "before_bytes": 10302,
    "before_sha256": "31964c800c86e79d6a0c7ba7c282960ba3cdb91dc0f9b89f92ac8384987692aa",
    "native_relative_path": "robosafebench/assets/data/realism_v3/packs/person_down/calibration/target_side.json",
    "pointers": [
      {
        "before_value_sha256": "244fd0f84b7a1d216c9fa3e2b1696891884de268a783a4acc0abb7f965242788",
        "pointer": "/source_spec",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/specs/a6_down_side.json"
      }
    ],
    "realism_relative_path": "packs/person_down/calibration/target_side.json"
  },
  {
    "before_bytes": 4320,
    "before_sha256": "db6b426281f5dc62b7aaa5e0160aad9c82155f2748843430995ce3638514f9d4",
    "native_relative_path": "robosafebench/assets/data/realism_v3/provenance/asset_registry_supplement.json",
    "pointers": [
      {
        "before_value_sha256": "8b352014bdbe7fe067c68a9431a18c218d57ccfa782e4f284be13eefd34d3ab9",
        "pointer": "/packs/hand/source_pack",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/pack.json"
      },
      {
        "before_value_sha256": "05a2a45d520a815d8078c2e28207db5c05924c4514dee14d23f0515903d37d24",
        "pointer": "/packs/hand/files/hd_L_sleeve.obj/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hd_L_sleeve.obj"
      },
      {
        "before_value_sha256": "1a31484d33cacc706d6f558f0492d04be5b6db972d09511a9574883f10c60534",
        "pointer": "/packs/hand/files/hd_L_sleeve.png/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hd_L_sleeve.png"
      },
      {
        "before_value_sha256": "a7c1ef5820c400783d92bca934c67394efef6c48d6cd7aa6e26e3ae94a1eb542",
        "pointer": "/packs/hand/files/hd_R_sleeve.obj/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hd_R_sleeve.obj"
      },
      {
        "before_value_sha256": "af145b4445f019498883aad7f80022d8c99c97772347806cc874ce15581cbc55",
        "pointer": "/packs/hand/files/hd_R_sleeve.png/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hd_R_sleeve.png"
      },
      {
        "before_value_sha256": "02f9a87d4a2c0846d2c4c1be34441014dd0f48330743f9796e4eeca9c94dedf9",
        "pointer": "/packs/hand/files/hl_L_sleeve.obj/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hl_L_sleeve.obj"
      },
      {
        "before_value_sha256": "ab6dd7501995cb701e0b92d052c5be532351634961c2c3f792af3aec64b63e31",
        "pointer": "/packs/hand/files/hl_L_sleeve.png/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hl_L_sleeve.png"
      },
      {
        "before_value_sha256": "2980539800916266a56a94e4359d190757633b33d5098cb0539b6738af690ae4",
        "pointer": "/packs/hand/files/hl_R_sleeve.obj/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hl_R_sleeve.obj"
      },
      {
        "before_value_sha256": "9aeb70b6199eabe659a261af4e887b0f6f99b6613a6432f0e1f07d7bca8732d1",
        "pointer": "/packs/hand/files/hl_R_sleeve.png/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hl_R_sleeve.png"
      },
      {
        "before_value_sha256": "71afdd69e591e8613b68a1e9fa6f85be3c7e722f169d0bebb015b90937dc1945",
        "pointer": "/packs/hand/files/hm_L_sleeve.obj/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hm_L_sleeve.obj"
      },
      {
        "before_value_sha256": "eb9a9b4c1fba39ec4487821421238a44f5593102b70f42e3a1d6f3aab8722529",
        "pointer": "/packs/hand/files/hm_L_sleeve.png/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hm_L_sleeve.png"
      },
      {
        "before_value_sha256": "91af57d112d908e16a1a219cc8feb2ae6730b31c394aa6b6950788babf01683c",
        "pointer": "/packs/hand/files/hm_R_sleeve.obj/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hm_R_sleeve.obj"
      },
      {
        "before_value_sha256": "98893d1dbd1621d842096c8e1ed8bc951633fea0481806c0fdd61e47a165942c",
        "pointer": "/packs/hand/files/hm_R_sleeve.png/previously_registered_source",
        "replacement": "historical-source://asset-build/runtime/pilot/out/v2/packs/hand/hm_R_sleeve.png"
      }
    ],
    "realism_relative_path": "provenance/asset_registry_supplement.json"
  },
  {
    "before_bytes": 31999,
    "before_sha256": "da0a2d2cb2008ea05df66a68cdfe43a9dc0ab3527e2d2aae23310f81dfe5eaab",
    "native_relative_path": "robosafebench/assets/data/realism_v3/provenance/final_catalog_config.json",
    "pointers": [
      {
        "before_value_sha256": "6ad84dd9ec79368b9a1fc27e117db22f6f66607786aa4ca03ad964ce30656d60",
        "pointer": "/out",
        "replacement": "historical-source://asset-build"
      },
      {
        "before_value_sha256": "edea6cb412106539c14a24a45a31869274811297176cab6a46bab3d376073463",
        "pointer": "/pilot",
        "replacement": "historical-source://tooling/realism_pilot"
      },
      {
        "before_value_sha256": "d36e38e02be6d67ad3a0147edad52aed412e9e91560cca65e59c9e83e24eae13",
        "pointer": "/code",
        "replacement": "historical-source://asset-build/runtime/code_final_registered"
      },
      {
        "before_value_sha256": "1db7271a2e9b682777e23d0f235aa8147164dbe1e40903a224da95e7f3505834",
        "pointer": "/python",
        "replacement": "historical-source://tooling/rsafe_regen/venv_mj381/bin/python"
      },
      {
        "before_value_sha256": "965b3ba0d81cf320d2b532f359bc229cdc3e88546824d3c7f522ed87bd2804bb",
        "pointer": "/mesh_python",
        "replacement": "historical-source://tooling/realism_pilot/venv/bin/python"
      },
      {
        "before_value_sha256": "9304c12ba233150f4b0de51ec7cf30d0506177ed73289f72f21ff9f7ce7eadf8",
        "pointer": "/blender",
        "replacement": "historical-source://tooling/render_promo/blender/blender-4.5.14-linux-x64/blender"
      },
      {
        "before_value_sha256": "fc5d8c257f4e6c5ea00f2c71f4d530fc7ed0ab4e0d3028ae08c3ce5c658abe75",
        "pointer": "/human_blender",
        "replacement": "historical-source://tooling/realism_pilot/tools/blender-4.2.20-linux-x64/blender"
      },
      {
        "before_value_sha256": "69d0d55dd65a1cfd1ebee248a01aa6c9c79d56f43e48b618ed10293b2ccddc74",
        "pointer": "/compat_source",
        "replacement": "historical-source://source-checkout/robosafe_realism_cpu"
      },
      {
        "before_value_sha256": "3448b253c4f557d68779ccdeda94402d2a7ec96236402b51d4685ce37127e25d",
        "pointer": "/asset_stages/v2",
        "replacement": "historical-source://asset-build/runtime/baseline"
      },
      {
        "before_value_sha256": "f5f542bceba50b0f427b45f629d2bbfd4577e48af2fbf0e9aaeb1c35c2ddc554",
        "pointer": "/asset_stages/v3",
        "replacement": "historical-source://asset-build/runtime/pilot_final"
      },
      {
        "before_value_sha256": "0d6341b7f0b70243dac27b0724e7001865c31320d85b22b78f69cda0991f0b2d",
        "pointer": "/render_code_snapshot",
        "replacement": "historical-source://asset-build/runtime/code_final_review"
      },
      {
        "before_value_sha256": "e69edeff78dbb93686958be979e1233aba9a1fae202a6a404caab874d44212be",
        "pointer": "/asset_registry_supplement",
        "replacement": "historical-source://asset-build/asset_registry_supplement.json"
      }
    ],
    "realism_relative_path": "provenance/final_catalog_config.json"
  },
  {
    "before_bytes": 5032,
    "before_sha256": "cae38da6b706304d0001aa688bab0b9d8d52c9fe5bbefd4d1810df57ed96848a",
    "native_relative_path": "robosafebench/assets/data/realism_v3/provenance/hand_rebuild_validation.json",
    "pointers": [
      {
        "before_value_sha256": "0acaded214e970b0e319469e68e8ae50ac01f357daa13c8bc635eae9bb1e999b",
        "pointer": "/private_pilot",
        "replacement": "historical-source://asset-build/runtime/hand_registered_rebuild/pilot"
      },
      {
        "before_value_sha256": "8cdd061387b1d898a71347a4835bd5f75fdfa0914d02eaa5b5f2ac73f7ab31c9",
        "pointer": "/source_pilot",
        "replacement": "historical-source://asset-build/runtime/pilot"
      },
      {
        "before_value_sha256": "61f78758c089eac3aa02c2ee4d59757a4e9ec46a92bd03558c1a28f87b317719",
        "pointer": "/variants/hl_L/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hl_L.glb"
      },
      {
        "before_value_sha256": "c749767d19f301eea33b4b20100fbac276eac191f40714a716f7059b9cb4bd7f",
        "pointer": "/variants/hl_R/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hl_R.glb"
      },
      {
        "before_value_sha256": "1eb5f1d2240bae0593d7a750e2b0da4f5e93d5d4c5b8f8b699f7c5297fb52b4a",
        "pointer": "/variants/hm_L/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hm_L.glb"
      },
      {
        "before_value_sha256": "6f43b3d463d09e3ecd48f0f9a83d6b5b2c8702c468cf624d642cd93a7a36ada5",
        "pointer": "/variants/hm_R/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hm_R.glb"
      },
      {
        "before_value_sha256": "7b7ae70872aaf7e01834b64ac10950328a743ed0521ffcb3030632b938436680",
        "pointer": "/variants/hd_L/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hd_L.glb"
      },
      {
        "before_value_sha256": "9aceb40aba0d5ba785096da047467cf3b8d77c788ea6ac2ddd8b9bb80c613765",
        "pointer": "/variants/hd_R/source_glb",
        "replacement": "historical-source://asset-build/runtime/pilot/out/humans/glb2/hd_R.glb"
      }
    ],
    "realism_relative_path": "provenance/hand_rebuild_validation.json"
  },
  {
    "before_bytes": 882,
    "before_sha256": "2c518a8ca7ae6cf270db4040af24b3fbf4ba007171450a5f67264e074c26b9c4",
    "native_relative_path": "robosafebench/assets/data/realism_v3/provenance/provenance.json",
    "pointers": [
      {
        "before_value_sha256": "f5f542bceba50b0f427b45f629d2bbfd4577e48af2fbf0e9aaeb1c35c2ddc554",
        "pointer": "/source_snapshot",
        "replacement": "historical-source://asset-build/runtime/pilot_final"
      },
      {
        "before_value_sha256": "2767fd742dfad29f172bc689dfaef1e3c90c1145a25be007e0b8f80e10616241",
        "pointer": "/repository",
        "replacement": "historical-source://non-public-source-repository"
      }
    ],
    "realism_relative_path": "provenance/provenance.json"
  },
  {
    "before_bytes": 524,
    "before_sha256": "e3b9e1d950421941a73330c8fe229f582cfa31992f2dafd36e2521e15fd41069",
    "native_relative_path": "robosafebench/assets/data/realism_v3/provenance/registration_validation.json",
    "pointers": [
      {
        "before_value_sha256": "e69edeff78dbb93686958be979e1233aba9a1fae202a6a404caab874d44212be",
        "pointer": "/registry",
        "replacement": "historical-source://asset-build/asset_registry_supplement.json"
      },
      {
        "before_value_sha256": "e800dd3330c699f09300990d99772d12f9486dac7f8442ba51dd1199ac981a58",
        "pointer": "/previous_reports",
        "replacement": "historical-source://asset-build/runtime/registration_history"
      }
    ],
    "realism_relative_path": "provenance/registration_validation.json"
  }
]''')


def require(value, message):
    if not value:raise ValueError('HOLD public source projection: '+message)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def value_digest(value, locator=False):
    return digest(value.encode() if locator else json.dumps(value,sort_keys=True,separators=(',',':')).encode())


def pointer_parts(pointer):
    require(isinstance(pointer,str) and pointer.startswith('/'), 'invalid fixed JSON pointer')
    return [part.replace('~1','/').replace('~0','~') for part in pointer[1:].split('/')]


def at(document,pointer):
    value=document
    for part in pointer_parts(pointer):value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def leaf_changes(before,after,prefix=''):
    require(type(before) is type(after), 'JSON type changed outside permitted string leaves')
    if isinstance(before,dict):
        require(set(before)==set(after), 'JSON object keys changed')
        out=[]
        for key in before:out+=leaf_changes(before[key],after[key],prefix+'/'+key.replace('~','~0').replace('/','~1'))
        return out
    if isinstance(before,list):
        require(len(before)==len(after), 'JSON list length changed')
        out=[]
        for i,(a,b) in enumerate(zip(before,after)):out+=leaf_changes(a,b,prefix+'/'+str(i))
        return out
    return [prefix] if json.dumps(before,sort_keys=True)!=json.dumps(after,sort_keys=True) else []


def regular(root,relative):
    path=root/relative
    require(not Path(relative).is_absolute() and '..' not in Path(relative).parts
            and (path.resolve()==root.resolve() or root.resolve() in path.resolve().parents), 'unsafe fixed package-relative path')
    require(path.is_file() and not path.is_symlink(), 'original projection file is not regular')
    return path


def prepare(source_root):
    root=Path(source_root).resolve();changes=[];payloads={};manifest_children={}
    require(len(ALLOWLIST)==20 and sum(len(row['pointers']) for row in ALLOWLIST)==57, 'fixed allowlist shape changed')
    for spec in ALLOWLIST:
        path=regular(root,spec['native_relative_path']);raw=path.read_bytes()
        require(len(raw)==spec['before_bytes'] and digest(raw)==spec['before_sha256'], 'original20-file bytes differ')
        before=json.loads(raw);encoded=raw;pointers=[];tokens={}
        for item in spec['pointers']:
            old=at(before,item['pointer']);replacement=item['replacement']
            require(isinstance(old,str) and digest(old.encode())==item['before_value_sha256'], 'original locator leaf differs')
            require(replacement.startswith('historical-source://') and not any(x in replacement for x in ('/gpfs/','/home/','/tmp/')), 'replacement is not a portable historical locator')
            old_token=json.dumps(old,ensure_ascii=False).encode();new_token=json.dumps(replacement,ensure_ascii=False).encode()
            previous=tokens.setdefault(old_token,[new_token,0]);require(previous[0]==new_token, 'ambiguous fixed replacement')
            previous[1]+=1
            pointers.append({'pointer':item['pointer'],'before_value_sha256':item['before_value_sha256'],
                             'after_value_sha256':digest(replacement.encode())})
        for old_token,(new_token,count) in tokens.items():
            require(raw.count(old_token)==count, 'locator token occurs outside exact allowed pointers')
            encoded=encoded.replace(old_token,new_token)
        after=json.loads(encoded)
        require(set(leaf_changes(before,after))=={item['pointer'] for item in spec['pointers']}, 'JSON changed outside exact locator pointers')
        for item in spec['pointers']:require(at(after,item['pointer'])==item['replacement'], 'fixed locator projection missing')
        payloads[spec['native_relative_path']]=encoded
        manifest_children[spec['realism_relative_path']]={'bytes':len(encoded),'sha256':digest(encoded)}
        changes.append({'native_relative_path':spec['native_relative_path'],'before_sha256':digest(raw),'after_sha256':digest(encoded),
            'before_bytes':len(raw),'after_bytes':len(encoded),'transform':'historical_source_locator_projection','pointers':pointers})
    path=regular(root,MANIFEST);raw=path.read_bytes()
    require(digest(raw)==BEFORE_MANIFEST_SHA256 and len(raw)==BEFORE_MANIFEST_BYTES, 'original manifest bytes differ')
    before=json.loads(raw);after=copy.deepcopy(before)
    require(len(before['files'])==687 and set(manifest_children).issubset(before['files']), 'manifest child set differs')
    pointers=[]
    for name,new in manifest_children.items():
        spec=next(row for row in ALLOWLIST if row['realism_relative_path']==name)
        require(before['files'][name]=={'bytes':spec['before_bytes'],'sha256':spec['before_sha256']}, 'manifest does not describe original child')
        after['files'][name]=new
        for field in ('bytes','sha256'):
            pointers.append({'pointer':'/files/'+name.replace('~','~0').replace('/','~1')+'/'+field,
                'before_value_sha256':value_digest(before['files'][name][field]),'after_value_sha256':value_digest(new[field])})
    require(set(leaf_changes(before,after))=={item['pointer'] for item in pointers}, 'manifest changed outside exact20 bytes/hash children')
    encoded=(json.dumps(after,sort_keys=True,indent=2)+'\n').encode()
    payloads[MANIFEST]=encoded
    changes.append({'native_relative_path':MANIFEST,'before_sha256':digest(raw),'after_sha256':digest(encoded),
        'before_bytes':len(raw),'after_bytes':len(encoded),'transform':'manifest_child_hash_refresh','pointers':pointers})
    return {'schema':SCHEMA,'rows':changes},payloads


def project(source_root,bridge_path,write_bridge=False):
    root=Path(source_root).resolve();bridge,payloads=prepare(root);bridge_path=Path(bridge_path)
    if write_bridge:
        require(not bridge_path.exists(), 'public bridge output already exists')
    else:
        expected=json.loads(bridge_path.read_bytes())
        require(expected==bridge, 'computed exact projection differs from public bridge')
    # All original inputs and all outputs are verified before any replacement.
    for relative,raw in payloads.items():
        path=regular(root,relative);temporary=path.with_name(path.name+'.public-projection-tmp')
        require(not temporary.exists(), 'temporary projection output already exists')
        with temporary.open('xb') as stream:stream.write(raw)
        temporary.chmod(path.stat().st_mode & 0o777);temporary.replace(path)
    if write_bridge:
        with bridge_path.open('x') as stream:json.dump(bridge,stream,sort_keys=True,indent=2);stream.write('\n')
    return bridge


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root',type=Path)
    parser.add_argument('bridge',type=Path)
    parser.add_argument('--write-bridge',action='store_true',help='Author bridge only from exact fixed original inputs')
    arguments=parser.parse_args()
    project(arguments.source_root,arguments.bridge,arguments.write_bridge)
