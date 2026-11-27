# 阶段八统计和费用口径

统计读取阶段七已经落库的 `gateway_request` 用量账本。当前数据库没有独立的 `ai_usage_record` 表。沿用真实账本可避免双写，平台费用和价格版本直接取调用记录，历史费用不会随新价目重算。首页、Token 统计和调用记录使用真实 API。

## 接口

| 路径 | 返回 |
| --- | --- |
| `GET /api/v1/dashboard/overview`、`/api/v1/usage/summary` | 同一汇总口径，包含 Token、调用、成功/失败/进行中、费用、活跃主体、平均响应时间、未知及未结算数量。 |
| `GET /api/v1/usage/trend` | 企业本地日期内的统计点。有账本记录的日期生成数据点。 |
| `GET /api/v1/usage/by-department`、`by-project`、`by-user`、`by-model`、`by-provider`、`by-key` | 依照各维度汇总。 |
| `GET /api/v1/usage/records`、`/api/v1/usage/records/{id}` | 分页明细及单条详情。越权详情返回 404。 |

统计接受 `period=today|yesterday|7d|30d|month|custom`，默认今天。自定义用企业本地 `start`、`end`（YYYY-MM-DD）且最多 90 个日历日，结束日包含当天，到当前时刻截断。可用 `user_id`、`department_id`、`project_id`、`key_id`、`provider_id` 和 `model_id` 叠加过滤。分页用 `page`、`size`。用 `APP_ENTERPRISE_TIMEZONE` 配置 PostgreSQL 可识别的 IANA 时区，默认 `Asia/Shanghai`。用本地午夜转换成 UTC 半开区间，由调用开始时间归属。趋势使用相同企业时区。

## 权限和计量

汇总、分组、分页总数与详情统一使用账本中冻结的用户与部门归属。普通用户看本人，部门主管看本人及获明确授权的部门，管理员看全企业。跨部门项目依旧逐调用应用权限。当前直接使用 PostgreSQL 聚合与现有时间和归属索引。响应设置 `private, no-store`，暂未启用 Redis 统计缓存。

费用按原币汇总为十进制字符串，仅计入已结算的平台费用，供应商账单单独保留。缓存 Token 为读缓存加写缓存，按账本用量直接展示。输入、输出和总量不把缓存作为额外 Token。没有归一化 usage 的记录仍进入调用数量和未知计数。未结算包括已预留及待核对。成功率使用成功数除以已完成调用数；活跃用户和 Key 按选定条件内的账本记录去重。平均响应时间使用账本记录的开始至终止时间，精度以现有账本为限。未落入用量账本的准入拒绝留在现有请求日志中。
