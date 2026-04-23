# 喵酱 · 昇腾 310 小助理

面向昇腾 310 场景的智能问答助手，聚焦 **MindIE / vLLM 310P / 部署与兼容性** 等常见问题，回答会附带证据与建议，适合做技术排查和方案对比。

## 在线使用

- 访问地址：<https://edge-agent.zeabur.app/>

![喵酱在线版预览](docs/images/preview.png)

## 你可以用它做什么

- 快速查询模型支持与兼容性信息
- 对比不同方案（例如 MindIE 与 vLLM 310P）
- 获取部署排障建议与检查清单
- 根据历史会话连续追问，逐步收敛问题

## 使用方法（3 步）

1. 打开在线页面：<https://edge-agent.zeabur.app/>
2. 在输入框直接提问（可先从下面示例复制）
3. 查看回答中的证据与建议，继续追问细化结论

## 推荐提问方式

- “MindIE 和 vLLM 310P 的核心差异是什么？”
- “我在 310 上启动失败，优先检查哪几项？”
- “Qwen3-32B 在当前环境是否支持？需要哪些前置条件？”
- “给我一个上线前自检清单，按优先级排序。”

## 数据与边界说明

- 当前知识源来自 `data/knowledge.json`
- 回答用于技术参考，请结合你当前版本的官方文档与实际环境验证

## 参考链接

- [喵酱在线入口](https://edge-agent.zeabur.app/)
- [MindIE-LLM 支持模型列表](https://gitcode.com/Ascend/MindIE-LLM/blob/master/docs/zh/user_guide/model_support_list.md)
