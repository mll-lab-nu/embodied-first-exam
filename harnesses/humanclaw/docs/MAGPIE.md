# Magpie 订阅接口部署与验证

这套配置让 HumanCLAW 通过 Magpie 使用部署者自己的 Codex / ChatGPT 订阅。
代码、配置模板和运行说明进入仓库；账号认证、网关密钥留在部署者自己的环境中。
本流程验证功能与部署，不包含 Azure 性能对照，也不承诺吞吐量提升。

```text
GPU 计算节点：HumanCLAW 实验程序 + simulator
                 ↓ Chat Completions 或 Responses
              Magpie 网关
                 ↓ 部署者的订阅认证
             OpenAI 云端模型
```

Magpie 无需 GPU。短验证可以将网关和实验放在同一个 Slurm GPU 作业中，结束时
一起停止。长期部署的位置由集群规则决定：如果使用登录节点，先确认允许该服务，
并确认计算节点能访问它。模型权重不在 Hyak 上运行。

## 1. 准备运行环境和固定版本

模型接口检查需要 Python 3.10+、项目依赖、`openai` 和 Pillow；不需要 CUDA。
完整仿真继续使用已准备好的 Habitat、motion weights、HSSD 和 GPU 环境，见
[Klone 部署说明](KLONE_EXPERIMENTS.md)。不要为了接口检查重新安装 GPU 软件栈。

```bash
python -m pip install -e . openai
```

固定使用 [Magpie v0.1.1230](https://github.com/yetone/magpie/releases/tag/v0.1.1230)，
选择与机器匹配的 CLI。校验 SHA-256 后再赋予执行权限：

| 系统 | Release 文件 | SHA-256 |
| --- | --- | --- |
| Linux x86_64 / Hyak | `magpie-cli-linux-amd64` | `28c0d38bcda16be956a0ec6a98427b8656959b325acf3c75a23c5d68d5de7b13` |
| Mac Apple Silicon | `magpie-cli-darwin-arm64` | `c923e15b103c2b6bd463587ce2a06d0f455ee84ab9c035881d9d84dfe3d3d0e9` |

以 Linux 为例，在自己的软件目录中运行：

```bash
curl --fail --location \
  https://github.com/yetone/magpie/releases/download/v0.1.1230/magpie-cli-linux-amd64 \
  --output magpie
sha256sum magpie
# 确认与上表一致，再执行：
chmod 700 magpie
./magpie --version
```

以下命令假设该版本的 `magpie` 已在 PATH 中。服务和管理命令要使用同一套
`XDG_CONFIG_HOME` / `XDG_CACHE_HOME`；如设置独立目录，请使用绝对路径并限制
目录权限为 700。不要把认证目录放进 Git。

```bash
umask 077
export DO_NOT_TRACK=1 MAGPIE_NO_STATS=1
magpie update auto off
```

## 2. 登录部署者自己的订阅

在网关所属的用户环境中，使用安装好的 Codex CLI：

```bash
codex login status
# 如尚未登录，执行下面的命令并在自己的浏览器完成授权：
codex login --device-auth
magpie accounts
```

先使用一个测试账号，确认 Magpie 识别了正确的账号。账号是否有目标模型权限，
以实际调用为准。不要提交或传递 `auth.json`、Magpie 登录文件或 ChatGPT 密码。
合作者可以独立登录自己的订阅，无需开发者的登录文件。

## 3. 启动网关并配置访问控制

**个人电脑上的本机测试**可以使用：

```bash
export MAGPIE_ADDR=127.0.0.1:3425
export GOMAXPROCS=1
magpie serve
```

在另一个终端设置调用参数：

```bash
export MAGPIE_BASE_URL=http://127.0.0.1:3425/v1
export MAGPIE_API_KEY=magpie
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost"
export no_proxy="$NO_PROXY"
```

这里的 `magpie` 是 SDK 所需的占位值，不是访问保护。固定版本允许本机回环
连接使用任意 token。同一台共享机器的其他用户也可能访问回环端口，因此
**不能直接把这个个人电脑配置用于共享的 Hyak 节点**。

**共享节点 / 跨节点部署**：绑定网关所在节点的具体内网接口地址，并启用网关密钥。
下面的地址是示例，必须替换为实际节点的地址；不要照抄示例 IP。

```bash
export MAGPIE_ADDR=10.0.0.10:3425
export GOMAXPROCS=1
# 将生成的密钥保存在当前用户私有文件中，不输出到作业日志：
magpie gateway-key add humanclaw > /absolute/private/path/magpie.key
chmod 600 /absolute/private/path/magpie.key
magpie serve
```

在实验进程中配置实际 URL，并从私有文件或密钥管理环境读取网关密钥：

```bash
export MAGPIE_BASE_URL=http://10.0.0.10:3425/v1
export MAGPIE_API_KEY="$(cat /absolute/private/path/magpie.key)"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost,10.0.0.10"
export no_proxy="$NO_PROXY"
```

把直连名单中的示例 IP 同样换成实际网关地址。Hyak 环境可能设置了全局 HTTP
代理；本机 MCP/Responses 端口和集群内网关都应直连，否则可能收到代理的 503。
保留用于访问外网的代理配置，只对上述地址配置 `NO_PROXY` / `no_proxy`。

用内网 HTTP 时，`allow_http=true` 是对该连接的显式选择。HTTP 不加密，应在
受信任的受控网络中使用；跨不受信任网络使用带有效证书的 HTTPS 或受保护的连接。
端口转发也必须实际验证鉴权，不能认为转发本身就修复了 Magpie 的回环访问行为。

在将来运行实验的节点检查访问控制：

```bash
# 共享模式下，这两条均应返回 401：
curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}\n' \
  "${MAGPIE_BASE_URL}/models"
curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}\n' \
  -H 'Authorization: Bearer invalid-test-key' "${MAGPIE_BASE_URL}/models"

# 正确密钥应返回模型列表；密钥通过 stdin 交给 curl，不写进命令参数：
printf 'Authorization: Bearer %s\n' "$MAGPIE_API_KEY" | \
  curl --noproxy '*' --fail --silent --show-error --header @- \
  "${MAGPIE_BASE_URL}/models"
```

如果未授权请求成功，先调整监听地址和访问控制，不在该共享配置上开展实验。
`127.0.0.1` 指当前机器，不能用于指代另一个登录节点或计算节点。

## 4. 验证真实模型调用

从模型列表确认 `codex/gpt-6-astra`。需要使用账号提供的其他模型时，显式设置
`MAGPIE_MODEL`；代码不会自动回退到 Azure 或其他模型。

```bash
python -m humanclaw_bench api-check \
  --model-config configs/models/magpie_codex_astra.json \
  --timeout 180
```

该命令通过正式 rollout 适配器发送**一个**图片与 JSON 请求，关闭 SDK 重试。
报告中的 `passed`、`request_ok`、`json_ok`、`image_check_ok` 应为 `true`。
它使用合成色块，不上传项目文件，不启动 simulator，不产生 benchmark 分数。
失败报告不打印原始服务响应或密钥。

配置行为：

| 字段 | 行为 |
| --- | --- |
| `base_url_env: MAGPIE_BASE_URL` | 必须设置；缺失时立即失败，不回退到默认云端 URL。包含 `/v1`，不要附加 `/responses` 或 `/chat/completions`。 |
| `api_key_env: MAGPIE_API_KEY` | 只读取环境中的网关访问凭证；`require_api_key` 禁止无声使用 `EMPTY`。 |
| `model_env: MAGPIE_MODEL` | 未设置时使用 `codex/gpt-6-astra`；保留 `codex/` 路由前缀。 |
| `send_max_tokens: false` | 不向该订阅通道发送长度参数。`max_tokens: 4096` 保留为适配器/客户端配置，**不代表上游硬性输出上限**。 |
| `send_temperature: false` | 不发送温度。 |
| `reasoning_effort: medium` | 普通模型入口请求的推理强度；原生 Codex/Pi 从 harness 配置读取，模板也为 `medium`。 |
| `request_timeout_seconds: 180`, `max_retries: 0` | 普通入口的 SDK 请求超时和重试上限。原生客户端有自己的重试行为，受 harness 总时限约束。 |

固定版本的 Codex 转发会移除部分长度/采样参数，改写 instructions，并强制上游
流式、`store=false`。实验日志记录到的是 HumanCLAW→Magpie 的请求边界，不是
Magpie 转换后的完整上游请求。不能把这些设置视为与其他通道完全等价。

## 5. 原生 Codex / Pi 接入

使用 `configs/harnesses/magpie_native.json`。将 `codex_command` / `pi_command`
配置为部署机器上已准备好的启动器；已有的 sandbox 启动器应继续使用。
此模板不包含开发者电脑的路径。

普通 HumanCLAW 入口使用 Chat Completions；原生入口使用 Responses。
原生模板通过 `responses_base_url_env` 读取同一个 `MAGPIE_BASE_URL`，使用 Bearer
认证，并显式允许受控网关的 HTTP。其他原生配置仍默认要求 HTTPS。
原生子进程只获得项目本地代理的临时访问凭证，上游网关凭证留在父进程。

先做不消耗订阅的原生协议检查：

```bash
python -m humanclaw_bench harness-check --harness codex \
  --harness-config configs/harnesses/magpie_native.json \
  --output outputs/magpie-native-check/codex
python -m humanclaw_bench harness-check --harness pi \
  --harness-config configs/harnesses/magpie_native.json \
  --output outputs/magpie-native-check/pi
```

该检查使用真实原生进程与模拟模型，验证图片、工具调用和连续对话。它不访问
Magpie，也不代表真实订阅或 GPU 验证已通过。原生入口的真实验证要执行下一节的
短实验，并检查实际 Responses 调用与环境动作记录。

## 6. 在 GPU 作业中运行短实验

先准备可访问的网关。使用已有 Slurm 模板；它假设网关已经启动，不会替用户登录
账号或启动常驻服务。将路径、Slurm account/partition 改成部署者自己的值：

```bash
export HC_ROOT=/absolute/cluster/workspace
export HC_REPO="$HC_ROOT/HumanCLAW"
export HC_PYTHON=/absolute/prepared/environment/bin/python
export HC_MODEL_CONFIG="$HC_REPO/configs/models/magpie_codex_astra.json"
export HC_SCENE_CONFIG=/absolute/prepared/hssd-hab.scene_dataset_config.json
export HC_OUTPUT="$HC_ROOT/outputs/magpie-short-check"
export HC_HARNESS=humanclaw_psv
export HC_MAX_STEPS=2
# MAGPIE_BASE_URL 和 MAGPIE_API_KEY 应已在当前环境中设置。
sbatch --account=YOUR_ACCOUNT --partition=YOUR_GPU_PARTITION \
  --gres=gpu:1 --time=00:15:00 \
  --output="$HC_ROOT/outputs/magpie-%j.out" \
  --error="$HC_ROOT/outputs/magpie-%j.err" \
  "$HC_REPO/tools/klone_experiment.sbatch"
```

若测试原生入口，先设置 `HC_HARNESS=codex` 或 `pi`，并设置
`HC_HARNESS_CONFIG=/absolute/path/to/magpie_native.json`。每次使用新的 `HC_OUTPUT`。
检查任务配置、模型调用、动作记录和最终状态；达到两步上限或模型正常停止均可
作为短流程检查结果，不能据此声称完成了正式 benchmark。

`HC_MAX_STEPS` 限制环境决策步数，不等于模型请求数；HumanCLAW 的 planner/verifier
和原生客户端可能在一步中发出多个请求。Slurm 时限负责限制整个验证作业。

## 7. 合作者接手与问题定位

合作者拉取同一提交，准备环境，安装相同版本的 Magpie，登录自己的订阅，配置
地址与网关密钥，再依次完成鉴权检查、API 检查和短 GPU 实验。可选的开发者订阅
是另一条明确配置的服务来源，不是运行代码的必要条件。

| 现象 | 检查 |
| --- | --- |
| 缺少 `MAGPIE_BASE_URL` / `MAGPIE_API_KEY` | 在提交作业的环境或当前用户私有 `.env` 中设置，确认作业继承了变量。不要将密钥写入 JSON。 |
| 401 / 403 | 网关密钥、监听地址、访问权限、订阅登录状态。 |
| 404 / 模型缺失 | `/v1/models`、`codex/` 前缀、账号实际模型权限。 |
| 429 | 账号或网关额度/并发限制；停止扩大请求量。 |
| 超时 / 连接失败 | 服务是否存活、计算节点到网关的网络、是否误用了另一台机器的回环地址。 |
| JSON / 图片检查失败 | 参数兼容性、完整返回内容、该账号模型的视觉能力。 |
| 原生启动失败 | Codex/Pi 路径、原生依赖、MCP 工具发现以及隔离启动器设置。 |

参考：[固定版本网关与认证行为](https://github.com/yetone/magpie/blob/v0.1.1230/docs/reference.md)、
[Codex 请求转换](https://github.com/yetone/magpie/blob/v0.1.1230/internal/provider/codex_request.go)、
[官方 Codex 认证说明](https://learn.chatgpt.com/docs/auth)。
