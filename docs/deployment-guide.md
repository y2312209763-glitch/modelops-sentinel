# 模型部署、接口测试与监控指南

本文说明如何把模型准备、vLLM 服务、接口测试和 Prometheus/Grafana 监控连成可验证的完整流程。

## 1. 部署前检查

```bash
nvidia-smi
docker --version
docker compose version
python3 --version
```

模型资源需求应以具体模型版本、权重精度、最大上下文和并行策略为准。下载后检查模型配置、tokenizer、权重分片和磁盘占用，避免将文件不完整误判为框架问题。

## 2. 使用 venv 准备环境

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install vllm modelscope
```

示例下载命令：

```bash
modelscope download --model <组织名/模型名> --local_dir <模型目录>
```

## 3. 启动 vLLM

下面的 MiniMax 参数来自特定实践环境，不应直接套用到其他模型：

```bash
export MODEL_PATH="<模型目录>"
export VLLM_API_KEY="<安全注入的密钥>"

SAFETENSORS_FAST_GPU=1 nohup vllm serve "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name MiniMax-M2.5 \
  --trust-remote-code \
  --enable-expert-parallel \
  --tensor-parallel-size 8 \
  --api-key "$VLLM_API_KEY" \
  --enable-auto-tool-choice \
  --tool-call-parser minimax_m2 \
  --reasoning-parser minimax_m2_append_think \
  > /var/log/vllm/model-start.log 2>&1 &
```

检查日志：

```bash
tail -f /var/log/vllm/model-start.log
```

## 4. 分层测试

### 健康检查

```bash
curl -fsS http://127.0.0.1:8000/health
```

### 对话检查

```bash
curl --fail-with-body http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${VLLM_API_KEY}" \
  -d '{
    "model": "MiniMax-M2.5",
    "messages": [{"role": "user", "content": "请回复 OK"}],
    "max_tokens": 32
  }'
```

验证 `choices[0].message.content` 非空，而不只是检查状态码。

### Metrics 检查

```bash
curl -fsS http://127.0.0.1:8000/metrics | head
```

vLLM 在 OpenAI 兼容服务端口上暴露 Prometheus 格式的 `/metrics`。不同版本可能使用不同指标名称。

## 5. 监控链路

| 组件 | 输入 | 输出 | 职责 |
| --- | --- | --- | --- |
| vLLM | 推理请求与引擎状态 | `/metrics` | 请求、token、延迟、队列与缓存 |
| Node Exporter | Linux 系统信息 | `:9100/metrics` | CPU、内存、磁盘和网络 |
| DCGM Exporter | NVIDIA DCGM | `:9400/metrics` | GPU、显存、温度和功耗 |
| Prometheus | 各 Metrics 端点 | 时序数据 | 抓取、存储与 PromQL 查询 |
| Grafana | Prometheus | Dashboard | 可视化与告警展示 |

启动配置见 [deploy/compose.yaml](../deploy/compose.yaml)。

## 6. 验收顺序

1. 模型权重加载完成。
2. `/health` 成功。
3. 对话接口返回非空内容。
4. `/metrics` 返回指标。
5. Prometheus Targets 全部为 `UP`。
6. Grafana 数据源测试成功。
7. Dashboard 产生业务和资源数据。

可以使用本项目 CLI 一次执行前五项中的关键检查：

```bash
modelops-sentinel \
  --vllm-url http://127.0.0.1:8000 \
  --model MiniMax-M2.5 \
  --api-key "$VLLM_API_KEY" \
  --prometheus-url http://127.0.0.1:9090
```

## 7. 常见问题

### 回答为空

- 检查模型与 tokenizer 是否完整。
- 确认 API 中的模型名和 `--served-model-name` 一致。
- 确认工具调用解析器和 reasoning parser 与模型匹配。
- 对比物理机与容器中的 vLLM、CUDA、PyTorch 版本。
- 从最小参数启动，再逐项增加并行与解析功能。

### CUDA OOM

- 降低上下文长度或并发量。
- 调整 tensor parallel / expert parallel。
- 检查其他进程的显存占用。
- 结合 DCGM 指标和服务日志判断 OOM 阶段。

### 外部无法访问

- 检查服务是否监听 `0.0.0.0`。
- 逐层检查本机、同网段、安全组、防火墙与反向代理。
- 只开放业务需要的端口，不直接关闭全部防火墙。

### Grafana No data

- 先在 Prometheus 执行相同 PromQL。
- 检查 Target 状态和 Dashboard 数据源 UID。
- 从 vLLM `/metrics` 确认当前版本的指标名称。
- 确认测试期间确实产生了推理流量。

