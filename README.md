# 槐栈夜场·可移式导向牌补拍分流

把读不清的点位照片派回巡拍班，在开场前换掉失真的导向资料。

模拟团队为 槐栈夜场导览组共 14 人，负责两处夜场的可移式导向牌布点、现场照片和志愿者导览资料。。巡拍员用手机拍入场导向牌，编辑把照片缩到志愿者手册的版面尺寸后手动核对箭头、文字和裁边。不清楚的按点位退回补拍。

- 旧手机和新手机的照片缩小之后清晰度差别很大，编辑很难靠缩略图判断。
- 灯膜反光、失焦和窄边裁切往往要等整批结束才发现，届时巡拍员已离开原区域。
- 为了少漏一张而整批退回，会让巡拍班在开场前多跑多个点位。

巡拍班导出的照片编号、覆盖点位、缩版测量值，以及编辑对历史图的发布或补拍定案。 领班拿带现场处置说明的派单补拍，可用照片由编辑核对箭头指向及实际位置后入册。

## 业务模块

| 模块 | 工作内容 | 核心实体 |
|---|---|---|
| 巡拍测量单 | CSV 校验、预览实测字段、以完整数据内容的 SHA-256 去重、追溯版本和下载原始数据 | 数据版本 |
| 分流试算 | 按版本与领域参数创建计算单，由独立进程计算；从排队、成功或失败状态追溯 | 计算单 |
| 补拍候选 | 按业务字段查看度量、比较与排序，下载计算结果 | 计算单及其结果 |
| 点位派发 | 对结果样本作签发或暂缓，记录理由，导出选中样本并查看审计时间线 | 交接记录 |

## 算法及口径

**代价加权 CART 与最小代价复杂度剪枝**。采用缩版对比度、亮斑覆盖率、文字边缘锐度和最小安全边距预测编辑结论。CART 用加权 Gini 生长，需补拍样本权重为漏派相对代价，可用样本权重为 1。每个剪枝候选只用建树历史拟合，以定剪枝历史的总误派代价选树并列时选叶数少的，再用独立的复盘历史报告误派和漏派。逐张输出真实条件路径、训练叶节点内未加权的补拍占比及现场处理动作。建树、定剪枝和复盘批次都需要两种标签，待处置行只接受空标签，项目要求批次号唯一。

录入参数 **漏派补拍的相对代价**，默认 3，允许范围 1–8。多派一次补拍记 1 单位。按漏掉一张明显有问题的照片所需折返与资料返工设定系数。

演示集 `huai-night_sign_contact_sheet_20261125.csv` 由 `backend/src/business/demo.py` 用固定数据或固定随机种子生成。工作台保留每次运行使用的输入版本、参数、结果和签审人。业务判断由服务端执行，前端图表直接读取返回的数值。

## 一天的工作剧本

1. 17:05，巡拍领班导入 huai-night_sign_contact_sheet_20261125.csv，包含 160 条已判照片记录与 8 条今日点位记录。
2. 17:15，编辑检查建树、定剪枝和复盘三段历史都录入了发布或补拍定案。
3. 17:20，领班把漏派代价设为 3，执行剪枝定参，查看独立复盘组的漏派与误派。
4. 17:30，东遮廊 HP-Q-01 亮斑覆盖达 67%，进入补拍队列，巡拍员按照条件路径检查高光遮挡。
5. 17:35，南桥楼梯 HP-Q-02 的文字对比度为 0.82，缩图边距 12%，建议保留。
6. 17:50，主管导出点位派发清单，安排东遮廊和小舞台巡拍路线。
7. 18:25，编辑将补拍图按统一缩版复查箭头与文字，再交志愿组入册。

## 快速启动

```sh
test -f .env || cp .env.example .env
docker compose config --quiet
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```

前端在 `http://127.0.0.1:18324`，API 文档在 `http://127.0.0.1:19324/docs`，数据库绑定 `127.0.0.1:17824`。重复运行种子命令保留已有账号和版本。测试验收后用 `docker compose down` 停机可保留数据卷。重置本地演示数据可用 `docker compose down -v --remove-orphans`。

| 角色 | 登录邮箱 | 权限 |
|---|---|---|
| 分析员 | analyst@demo.local | 导入数据、提交计算、查看及导出 |
| 复核员 | reviewer@demo.local | 查看及导出、选择样本、签发或暂缓 |
| 观察员 | viewer@demo.local | 查看及导出已有内容 |

三个演示角色密码均为 `Yangfan-demo-2026`。Compose 默认绑定回环地址。自备数据可关闭 `SEED_DEMO`，并为需登录的环境另配账号和密钥。

## 技术与配置

| 服务 | 技术与职责 |
|---|---|
| frontend | HTML/CSS/JS ES 模块，Nginx 静态页面与同源 API |
| backend | Python 3.11、FastAPI、SQLAlchemy、JWT |
| worker | Python 后台进程，使用 DB 的原子认领、租约与重试，输出 CSV |
| db | PostgreSQL 16，存账号、版本、计算单和审计 |
| redis | Redis 7，通知 worker 尽快拾取，任务状态由数据库持久化 |

`FRONTEND_PORT`、`BACKEND_PORT`、`DB_PORT` 管理回环端口，`JWT_SECRET` 为签名密钥，`DB_PASSWORD` 为应用数据库口令，`COMPOSE_PROJECT_NAME` 控制该栈的命名空间。

本地 Python 开发可用 `docker compose up -d db` 启动关系库，并另起一个仅绑定回环的 Redis。Compose 内的 Redis 通过容器网络连接。用 Python 3.11 安装 `backend/requirements.txt` 后，进入 backend 目录，设置 `DATABASE_URL`、`REDIS_URL`、`JWT_SECRET`、`ARTIFACTS_DIR`、`SEED_DEMO`，分别运行 `uvicorn src.main:app --reload`、`python -m src.worker`。ARTIFACTS_DIR 需已存在且由两进程共享。前端可使用 Compose Nginx 镜像并重建以加载修改，或用已有 Nginx 反向代理本地 Python 端口。

`backend/src/business/` 保存本题字段、生成器和算法，`backend/src/services/` 处理资源生命周期，`backend/migrations/` 是初始关系模式，`frontend/src/` 按页面、API、会话、组件、路由及样式组织。前后端枚举分别在 `backend/src/constants/workflow.py` 和 `frontend/src/constants/enums.js`。角色用于 JWT 路由与表单权限，计算状态用于队列与结果页，签审决定用于交接页、审计和签发导出。

## 许可证

批次交付保留原作者权利。单独使用与再分发条款由项目所有者确定。
