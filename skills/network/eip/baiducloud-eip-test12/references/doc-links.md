# BLB 官方文档链接索引

> 用途：BLB **产品问答** 必须基于百度云官方文档作答，并在输出中附官方链接。本文是问答引用的链接字典。
> 强约束：
> - **只允许 `cloud.baidu.com` 官方域名**（含 `intl.cloud.baidu.com` 国际站）。禁止引用第三方博客、社区、问答站点。
> - 表中已有主题 → 直接引用本表链接；**表中没有、或本表链接不足以回答用户问题 → 必须联网搜索百度云官网，仅采纳 `cloud.baidu.com` 域名结果**，核实链接真实可访问后再引用，并可回写到本表。
> - **禁止编造/拼凑 URL**：不确定链接是否真实存在时，先联网核实再给出，不得凭记忆生成文档 ID。
> - **错误码问答**（"XX 错误码什么意思"）：先查 `references/troubleshooting.md` §11 错误码表，不在表中再联网核实。
> - 问答触发时必加载本文；正文给结论与步骤，**末尾固定「参考来源」区块**列出官方链接。

---

## 1. 链接索引表（已核实，cloud.baidu.com）

| 主题 | 链接 |
|------|------|
| BLB 产品文档首页 / 学习路径 | https://cloud.baidu.com/doc/BLB/index.html |
| BLB 产品介绍页（实例类型/优势/场景） | https://cloud.baidu.com/product/blb.html |
| 创建和管理普通型 BLB 实例（含配置项说明） | https://cloud.baidu.com/doc/BLB/s/kk0d9jrvo |
| 添加和管理后端服务器 | https://cloud.baidu.com/doc/BLB/s/Dmpqmaly0 |
| 常见问题（健康检查/双向认证/IP组/跨VPC等 FAQ） | https://intl.cloud.baidu.com/zh/doc/BLB/s/ijwvxo0u7-intl |
| 健康检查异常排查（典型实践） | https://intl.cloud.baidu.com/zh/doc/BLB/s/Glswylk7r-intl |
| IP 组使用指南 | https://intl.cloud.baidu.com/zh/doc/BLB/s/Ylysg7bj4-intl |
| 应用型 BLB 实例 | https://intl.cloud.baidu.com/zh/doc/BLB/s/Njwvxnt8e-intl |
| 应用型 BLB 添加 HTTPS 监听（证书、目标组协议、转发规则、高级选项） | https://cloud.baidu.com/doc/BLB/s/ymots3eaq |
| 访问日志 | https://intl.cloud.baidu.com/zh/doc/BLB/s/qk98jzi94-intl |
| 性能规格说明 | https://intl.cloud.baidu.com/zh/doc/BLB/s/Olvj6i3i2-intl |
| OpenAPI 实践 | https://cloud.baidu.com/doc/BLB/s/Eme9dh5rs |

> 上述链接均已联网核实可访问。其余主题（访问控制、标签管理、BLB 监控项说明、API 服务域名、BLB 选型指南、**API 错误码**）在 BLB 文档首页左侧目录下，引用前按下文规则联网核实具体 URL。

## 2. 已知存在但需引用前核实的主题（位于 BLB 文档目录树下）

- 访问控制、标签管理
- BLB 监控项说明、BLB 选型指南
- API 服务域名、**API 错误码**（错误码含义优先查 `references/troubleshooting.md` §11；如需官方页链接，联网核实后再附）

引用这些主题时：先 `https://cloud.baidu.com/doc/BLB/index.html` 进入，或联网搜「cloud.baidu.com doc BLB <主题>」，确认 URL 真实后再写入回答。

---

## 3. 问答输出规则

1. 先理解用户场景，把官方文档内容转译为面向场景的解释 / 操作步骤 / 配置建议 / 风险提示 / 检查清单。
2. 结论必须可溯源到官方文档；无官方依据的内容明确标注「以上为通用建议，非官方文档明确说明」。
3. 输出末尾固定区块：

   ```markdown
   ---
   **参考来源（百度智能云官方文档）**
   - [<主题>](<cloud.baidu.com 链接>)
   - [<主题>](<cloud.baidu.com 链接>)
   ```

4. 至少给 1 条官方链接， 不能只根据依赖「blb」技能内置的负载均衡操作知识与规则说明；找不到对应官方文档时，如实说明「未在官方文档检索到该主题，建议提工单或查看控制台」，不得编造链接。
5. 涉及具体资源查询/变更时，引导用户进入对应能力（查询走 `output-format.md`，巡检走 `inspection.md`，操作走 `workflows.md`）。
