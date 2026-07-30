# 微信拍一拍随机回复器

这是一个实验性的 Windows 桌面自动化程序。它用 Windows OCR 扫描微信左侧
可见会话列表；发现新的 `tickled m`（同时匹配 `tickled me` 和
`tickled my`）后，打开对应会话并发送随机回复。

[直接下载 Windows 版本](https://github.com/DouYe/wechat-pat-responder/releases/latest/download/WeChatPatResponder-Windows-x64.zip)
· [English](README.md)

## 功能

- 监控左侧可见会话，不要求目标会话已经打开。
- 目标已经是当前会话时跳过点击，避免把会话点成未选中。
- 记录微信显示时间和本机检测时间。
- 支持连续拍、持久计数和 2.5 秒最短去重。
- 随机行为：Google Doc 实时词条、计数器、连击、假系统文字、红包兑奖彩蛋。
- Google Doc 实时词条占 90%，计数器 4%，连击 3%，假系统消息 2%，红包彩蛋 1%。
- 程序会直接读取公开的
  [Google Doc 词条源](https://docs.google.com/document/d/1zaxLelnWjSDkGEm1SFQnPh643NF7KGJXdcfjVFv7QdM/edit?tab=t.0)
  ；启动时自动读取一次。文档有新词条后点击 **Reload 文档** 即可导入，不需要
  重启或重新发布版本；拍一拍触发时不会联网读取。
- 启动读取和 Reload 都在后台执行，网络超时提高到 90 秒，并以 512 KB 分块解析；
  Reload 按钮会显示已下载 MB。大文档读取期间界面和 OCR 监控仍可继续使用。
- 保持文档中的行为顺序。一级编号是一次随机行为，二级条目会按显示顺序作为额外的
  独立消息发送。
- 支持把“只有图片的一级编号”作为随机图片行为。图片只会在启动或点击
  **Reload 文档** 时下载，按内容哈希保存在本机；抽中后通过 Windows 图片剪贴板
  粘贴到微信发送。
- `google_doc_media` 内会保存图片来源索引；后续 Reload 遇到没有变化的旧图片时，
  直接复用已经验证过的缓存文件，不再重复进行 Base64 解码和图片校验。
- 每次成功加载都会按原顺序保存到本地缓存。Google Docs 临时不可用时，继续使用最近
  一次成功缓存，不会让回复功能直接失效。
- 每个会话独立进行无放回抽取；整套回复全部用完后才开始新一轮，而且新一轮
  第一条不会紧接着重复上一条。
- 红包彩蛋只发文字，不会执行支付。
- 不修改微信、不注入 DLL、不读取聊天数据库。

## Google Doc 词条格式

- 一级编号：一个随机行为。
- 缩进的二级编号：属于上一个一级行为，程序会按顺序分别发送。
- 同一个编号内写 `↵`：在同一条微信消息里换行；写 `↵ ↵` 会保留一个空白行。
- 图片单独放在一个一级编号中：该编号会成为一条随机图片行为。支持 PNG、JPEG、
  GIF 和 WebP；动图发送时使用第一帧。

```text
1. “疯狂是不断的尝试一件事情 并期待不同的结果” - 爱因斯坦
   a. 而你我的朋友 非常疯狂
2. 第一行 ↵ 第二行 ↵ ↵ 最后一段
```

程序本身不会截断回复，但微信仍可能实施自己的单条消息长度限制。
只要不修改已有词条的文字，每个会话原来的去重记录会继续有效；追加到末尾的新词条
会自动加入尚未使用的候选池。

Google 的公开 HTML 导出每次仍会传输完整文档，本身没有免登录的增量读取接口。
因此以后如果加入尺寸特别大的图片，建议插入文档前先压缩；这样能直接降低每次
Reload 的下载量。即使如此，后台读取期间也不会阻塞监控，失败时仍继续使用上一次
成功缓存。

## 支持范围

发行包支持 **64 位 Windows 10/11**。程序依赖 Windows 微信、Windows OCR、
窗口截图和 Windows 输入接口，因此不能原生运行在 macOS、Linux 或 Chromebook。
其他系统可以连接一台常开的 Windows 主机或使用 Windows 虚拟机。

## 最快安装方式

1. 安装并登录官方 Windows 微信/Weixin。
2. 安装英文 OCR：
   - 设置 → 时间和语言 → 语言和区域；
   - 添加“英语（美国）”及其语言功能；
   - 或下载源码后，以管理员身份运行 `Install-OCR.cmd`。
3. 下载并解压
   [WeChatPatResponder-Windows-x64.zip](https://github.com/DouYe/wechat-pat-responder/releases/latest/download/WeChatPatResponder-Windows-x64.zip)。
4. 保持微信主窗口打开且没有最小化。
5. 双击 `Run.cmd`。
6. 点击“开始监控”。首次扫描只建立基线，需要让对方重新拍一次。

由于程序未购买代码签名证书，Windows SmartScreen 可能显示警告。介意的话请先
检查源码并自行构建。

## 从源码安装

需要 64 位 Python 3.10 或更新版本。下载源码后双击：

```bat
Setup.cmd
```

脚本会创建独立 `.venv`、安装依赖、检查 OCR 并启动程序。以后使用
`Run.cmd` 即可。

如果 OCR 检查失败，请以管理员身份运行：

```bat
Install-OCR.cmd
```

完成后重启 Windows。也可以参考微软的
[Windows 语言包说明](https://support.microsoft.com/zh-cn/windows/windows-%E7%9A%84%E8%AF%AD%E8%A8%80%E5%8C%85-a5094319-a92d-18de-5b53-1cfc697cfca8)。

## 排错

- 点击“单次 OCR 测试”，确认左栏预览中能读到 `tickled m`。
- 目标会话必须出现在左侧可见区域。
- 微信可以被其他窗口遮挡，但不能最小化。
- OCR 读不到时，尝试放大微信窗口和左侧会话栏。
- 微信更新界面后，OCR 区域和点击位置可能需要调整。

## 风险说明

这不是微信官方接口。自动点击可能因 OCR 或界面变化选错会话；程序还会覆盖目标
输入框内尚未发送的文字。建议先用备用号测试，并阅读 [SECURITY.md](SECURITY.md)。

## 数据文件

- `tickle_events.log`：检测历史
- `reply_history.txt`：按会话 ID 记录每次成功发送的类型和完整回复，可在程序里
  点击“打开发送记录”查看
- `tickle_state.json`：各会话累计次数、连击、已发送回复和无重复进度
- `google_doc_replies_cache.json`：最近一次成功载入的有序文字/图片回复快照
- `google_doc_media`：从 Google Doc 下载的本地图片缓存

项目采用 MIT License，与腾讯、微信、Weixin 无关联。
